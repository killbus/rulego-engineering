// Generic Resin adapter: no alert, channel name, or content extraction policy.
var request = typeof msg === 'string' ? JSON.parse(msg) : msg;
if (!request || typeof request !== 'object' || Array.isArray(request)) {
  throw new Error('resinSubscriptionUpdate: expected {id, body}');
}
if (typeof request.id !== 'string' ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(request.id)) {
  throw new Error('resinSubscriptionUpdate: id must be a canonical UUID');
}
if (!request.body || typeof request.body !== 'object' ||
    Array.isArray(request.body) || Object.keys(request.body).length === 0) {
  throw new Error('resinSubscriptionUpdate: body must be a non-empty JSON object');
}

var baseUrl = vars.baseUrl;
if (typeof baseUrl !== 'string' || baseUrl.indexOf('$' + '{') !== -1 ||
    !/^https?:\/\/[^\s\/?#@]+(?:\/[^\s?#]*)?$/.test(baseUrl)) {
  throw new Error('resinSubscriptionUpdate: configure baseUrl as an HTTP(S) service URL');
}
if (typeof vars.adminToken !== 'string' || !vars.adminToken.trim() ||
    vars.adminToken.indexOf('$' + '{') !== -1 || /[\r\n]/.test(vars.adminToken)) {
  throw new Error('resinSubscriptionUpdate: configure adminToken');
}

metadata.resin_subscription_id = request.id.toLowerCase();
metadata.resin_request_url = baseUrl.replace(/\/+$/, '') +
  '/api/v1/subscriptions/' + metadata.resin_subscription_id;

// restApiCall sends msg as JSON. Never concatenate content into a JSON template.
// Resin owns field validation, source_type compatibility, and update side effects.
return {
  msg: request.body,
  metadata: metadata,
  msgType: msgType,
  dataType: 'JSON'
};
