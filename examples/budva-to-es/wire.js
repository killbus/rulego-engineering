// Budva wire node: the SINGLE owner of crypto and raw-byte handling.
//
// This file is the BODY of the jsTransform script for node_wire (chain.json
// embeds crypto.js + this file byte-identically, drift-guarded; the guard
// also asserts parser.js and events.js contain no crypto symbol, so this
// node is the only place bytes and hashes are touched).
//
// Input (after endpoint processors ["toHex","headersToMetadata"]):
//   msg      = UPPERCASE hex of the exact raw request body (toHex)
//   metadata = all request headers (incl. optional X-Budva-Signature)
//   global.budva_hmac_key = shared HMAC key ("") = verification off
//
// What it does, in one place:
//   1. decodes the exact wire bytes (never re-serializes to compare)
//   2. gates on an optional HMAC over those exact bytes (signature missing
//      or mismatched -> throw -> 400, reason prefixed "budva-wire: hmac ...")
//   3. PUBLISHES the audit identity: metadata.audit_id =
//      sha256Hex(exact raw body) — a hex string, no byte carrier needed
//      downstream (the audit branch consumes it as data)
//   4. delivers the downstream nodes a plain string msg = the UTF-8 decoded
//      raw body (TEXT data type) — parser.js then JSON.parses that text
//
// Why one node: jsTransform nodes cannot call each other's functions (each
// node is an isolated VM; there is no import in chain files). The
// "capability atomic" for crypto is therefore a NODE that computes and
// publishes values other nodes consume, instead of inlining the same crypto
// source into every consumer (which duplicated it in the running chain).
//
// On any failure this body throws -> node routes Failure -> the endpoint
// responds 400 with the reason (responseToBody, spike-verified).

try {
  // 1. msg is uppercase-hex(raw request body) per the toHex processor.
  var rawBytes = hexToBytes(msg);

  // 2. HMAC gate. Key empty => verification off (matches Budva: no secret ->
  //    no signature header sent). Key set => signature mandatory + must verify.
  var key = '';
  if (typeof global !== 'undefined' && global) key = String(global.budva_hmac_key || '');
  if (key !== '') {
    var sig = metadata['X-Budva-Signature'] || metadata['x-budva-signature'] || '';
    if (sig.indexOf('sha256=') !== 0) throw new Error('budva-wire: hmac signature missing or malformed');
    var expected = bytesToHex(hmacSha256Bytes(utf8Encode(key), rawBytes));
    if (!ctEqualHex(sig.slice(7), expected)) throw new Error('budva-wire: hmac signature mismatch');
  }

  // 3. Publish the audit identity (single source for budva-events-v1 _id).
  metadata.audit_id = bytesToHex(sha256Bytes(rawBytes));

  // 4. Deliver the decoded body as a plain string (TEXT).
  return {
    msg: utf8Decode(rawBytes),
    metadata: metadata,
    msgType: msgType,
    dataType: 'TEXT'
  };
} catch (err) {
  throw err;
}
