try {
  // 1. msg is uppercase-hex(raw request body) per the toHex processor.
  var rawBytes = hexToBytes(msg);

  // 2. HMAC gate. Key empty => verification off (matches Budva: no secret ->
  //    no signature header sent). Key set => signature mandatory + must verify.
  var key = '';
  if (typeof global !== 'undefined' && global) key = String(global.budva_hmac_key || '');
  if (key !== '') {
    var sig = metadata['X-Budva-Signature'] || metadata['x-budva-signature'] || '';
    if (sig.indexOf('sha256=') !== 0) throw new Error('budva-parse: hmac signature missing or malformed');
    var expected = bytesToHex(hmacSha256Bytes(utf8Encode(key), rawBytes));
    if (!ctEqualHex(sig.slice(7), expected)) throw new Error('budva-parse: hmac signature mismatch');
  }

  // 3. Parse from the exact raw bytes (never re-serialize to compare/verify).
  var obj;
  try { obj = JSON.parse(utf8Decode(rawBytes)); }
  catch (pe) { throw new Error('budva-parse: body is not valid JSON'); }
  if (!obj || typeof obj !== 'object') throw new Error('budva-parse: body is not a JSON object');
  if (obj.schema_version !== 2) throw new Error('budva-parse: unsupported schema_version ' + obj.schema_version);
  var event = obj.event;
  if (event !== 'new' && event !== 'edited' && event !== 'deleted') throw new Error('budva-parse: unknown event ' + event);
  if (typeof obj.occurred_at !== 'string' || obj.occurred_at === '') throw new Error('budva-parse: missing occurred_at');
  var m = obj.message;
  if (!m || typeof m !== 'object') throw new Error('budva-parse: missing message');
  if (typeof m.chat_id !== 'number' || !isFinite(m.chat_id)) throw new Error('budva-parse: missing chat_id');
  if (typeof m.message_id !== 'number' || !isFinite(m.message_id)) throw new Error('budva-parse: missing message_id');

  // 4. Build the single-index elasticsearchWrite message (plugin contract).
  //    _id stable per message; op "index" = unconditional overwrite (LWW by
  //    occurred_at). deleted => tombstone doc (the node cannot issue deletes).
  var id = String(m.chat_id) + ':' + String(m.message_id);
  var doc = {
    event: event,
    occurred_at: obj.occurred_at,
    chat_id: m.chat_id,
    message_id: m.message_id
  };
  if (event === 'deleted') {
    doc.tombstone = true;
    doc.delete = (m.delete && typeof m.delete === 'object') ? m.delete : null;
  } else {
    doc.tombstone = false;
    doc.sent_at = (typeof m.sent_at === 'string') ? m.sent_at : null;
    doc.edited_at = (typeof m.edited_at === 'string') ? m.edited_at : null;
    doc.sender = (m.sender && typeof m.sender === 'object') ? m.sender : null;
    doc.content = (m.content && typeof m.content === 'object') ? m.content : null;
    doc.reply_to = (m.reply_to && typeof m.reply_to === 'object') ? m.reply_to : null;
    doc.forward = (m.forward && typeof m.forward === 'object') ? m.forward : null;
    doc.message_thread_id = (typeof m.message_thread_id === 'number') ? m.message_thread_id : 0;
    doc.has_sensitive_content = (m.has_sensitive_content === true);
    doc.restriction_reason = (typeof m.restriction_reason === 'string') ? m.restriction_reason : '';
  }

  return {
    msg: JSON.stringify({
      index: 'budva-messages-v1',
      operations: [{ op: 'index', id: id, doc: doc }]
    }),
    metadata: metadata,
    msgType: msgType,
    dataType: 'JSON'
  };
} catch (err) {
  throw err;
}
