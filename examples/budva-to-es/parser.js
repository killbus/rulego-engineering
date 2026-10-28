// Budva schema v2 parser for the generic elasticsearchWrite node.
//
// This file is the BODY of the jsTransform script (the value of the node
// configuration's "jsScript"). At deploy time the node wraps it as
//   function Transform(msg, metadata, msgType, dataType) { <this body> }
// (rulego components/transform JsTransformFuncTemplate); chain.json embeds
// it byte-identically (drift-guarded, and the guard asserts this script
// contains NO crypto symbol — see parser_test.go).
//
// It is PURE BUSINESS LOGIC. All byte-level and crypto work happened
// upstream in node_wire (crypto.js + wire.js): the HMAC gate already ran
// over the exact wire bytes, and node_wire published
//   metadata.audit_id = a hex digest of the exact raw body (see wire.js)
// and delivered this node a plain string msg = the decoded raw body
// (wire node's output, TEXT data type). This node parses and validates;
// it never touches raw bytes or any hashing/signing (all of that is
// node_wire's responsibility, see wire.js).
//
// Output: the elasticsearchWrite single-index message (plugin contract,
// rulego-elasticsearch client.go) for budva-messages-v1. On any contract
// violation this body throws -> the node routes Failure -> the endpoint
// responds 400 with the reason (responseToBody).

try {
  // 1. Parse from the decoded raw body (node_wire decoded the exact wire
  //    bytes; JSON text is unchanged by the decode).
  var obj;
  try { obj = JSON.parse(msg); }
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

  // 2. Build the single-index elasticsearchWrite message (plugin contract).
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
