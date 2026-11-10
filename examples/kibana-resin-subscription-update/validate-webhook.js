// Public webhook envelope only. Workflow selection belongs to the switch node.
var envelope = typeof msg === 'string' ? JSON.parse(msg) : msg;
if (!envelope || typeof envelope !== 'object' || Array.isArray(envelope)) {
  throw new Error('kibana-webhook-ingress: expected a webhook object');
}
if (envelope.schema_version !== 1) {
  throw new Error('kibana-webhook-ingress: schema_version must be 1');
}
if (!envelope.payload || typeof envelope.payload !== 'object' || Array.isArray(envelope.payload)) {
  throw new Error('kibana-webhook-ingress: payload must be an object');
}
// Keep optional source trace data when downstream nodes replace msg.
// Do not copy the payload or arbitrary envelope fields into metadata.
var traceFields = ['rule_id', 'rule_name', 'alert_id', 'timestamp'];
for (var i = 0; i < traceFields.length; i++) {
  var field = traceFields[i];
  var value = envelope[field];
  if (typeof value === 'string' && value.trim()) {
    metadata['kibana_' + field] = value;
  }
}
return { msg: envelope, metadata: metadata, msgType: msgType, dataType: 'JSON' };
