// Budva audit-branch projection for the generic elasticsearchWrite node.
//
// This file is the BODY of the jsTransform script (the value of the node
// configuration's "jsScript"). At deploy time the node wraps it as
//   function Transform(msg, metadata, msgType, dataType) { <this body> }
// (rulego components/transform JsTransformFuncTemplate), and the chain embeds
// crypto.js + this file byte-identically (drift-guarded by parser_test.go).
//
// It is a PURE PROJECTION of the parser's validated output. The parser
// (parser.js) is the single owner of validation: HMAC over the exact wire
// bytes and strict schema v2 checks already ran upstream, and this branch
// only exists for the messages it emitted. The engine hands a JSON data type
// to jsTransform as a PARSED object (components/base base.go GetDataByType),
// so msg is the messages contract:
//   msg      = { index, operations: [{ op, id, doc }] }
//   metadata = { rawHex, ...request headers }  (rawHex stamped by the parser
//              = the toHex hex carrier of the exact raw request body)
//
// Output: the elasticsearchWrite single-index message (plugin contract,
// rulego-elasticsearch client.go) for budva-events-v1:
//   _id = sha256Hex(exact raw body bytes)  -> a redelivered body is the same
//   _id, op "create" -> ES 409 duplicate, classified duplicate by the plugin
//   (idempotent success; the audit index is append-only delivery log).
// Any contract violation throws -> the node routes Failure -> the endpoint
// responds 400 with the reason (responseToBody, spike-verified).

try {
  var op = msg.operations && msg.operations[0];
  if (!op || typeof op.doc !== 'object' || !op.doc) {
    throw new Error('budva-events: missing operations[0].doc');
  }
  var d = op.doc;
  if (typeof d.chat_id !== 'number' || typeof d.message_id !== 'number') {
    throw new Error('budva-events: doc missing chat_id/message_id');
  }

  var rawHex = String(metadata.rawHex || '');
  if (rawHex === '' || rawHex.length % 2 !== 0) {
    throw new Error('budva-events: missing metadata.rawHex');
  }
  var id = bytesToHex(sha256Bytes(hexToBytes(rawHex)));

  return {
    msg: JSON.stringify({
      index: 'budva-events-v1',
      operations: [{
        op: 'create',
        id: id,
        doc: {
          event: d.event,
          occurred_at: d.occurred_at,
          chat_id: d.chat_id,
          message_id: d.message_id,
          // Server receipt time (goja Date, RFC3339). On redelivery the first
          // doc wins (op create, 409), so received_at is the FIRST sight.
          received_at: new Date().toISOString()
        }
      }]
    }),
    metadata: metadata,
    msgType: msgType,
    dataType: 'JSON'
  };
} catch (err) {
  throw err;
}
