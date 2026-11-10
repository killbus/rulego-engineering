// Business mapping only: extract the first HTTP(S) subscription URL in text order.
// The next jsFilter drops messages without a URL before the adapter is invoked.
// Input is the validated envelope, selected by Route by workflow.
var payload = msg.payload;
var text = typeof payload.message_content === 'string' ? payload.message_content : '';
var candidates = text.match(/https?:\/\/[^\s<>"'`，。；！？、【】「」『』（）]+/gi) || [];
var url = '';
for (var i = 0; i < candidates.length; i++) {
  var candidate = candidates[i];
  // Remove prose punctuation and unmatched closing brackets (e.g. Markdown links),
  // while preserving balanced parentheses in a URL path and IPv6 host brackets.
  var previous;
  do {
    previous = candidate;
    candidate = candidate.replace(/[.,;!]+$/, '');
    var pairs = [['(', ')'], ['[', ']'], ['{', '}']];
    for (var j = 0; j < pairs.length; j++) {
      var open = pairs[j][0];
      var close = pairs[j][1];
      if (candidate.slice(-1) === close &&
          candidate.split(close).length > candidate.split(open).length) {
        candidate = candidate.slice(0, -1);
      }
    }
  } while (candidate !== previous);
  if (/^https?:\/\/[^\/?#]+(?:[\/?#]|$)/i.test(candidate)) {
    url = candidate.replace(/^https?:/i, function (scheme) { return scheme.toLowerCase(); });
    break;
  }
}

return {
  msg: {
    id: payload.subscription_id,
    body: { url: url }
  },
  metadata: metadata,
  msgType: msgType,
  dataType: 'JSON'
};
