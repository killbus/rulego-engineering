// Budva schema v2 parser for the generic elasticsearchWrite node.
//
// This file is the BODY of the jsTransform script (the value of the node
// configuration's "jsScript"). At deploy time the node wraps it as
//   function Transform(msg, metadata, msgType, dataType) { <this body> }
// (rulego components/transform JsTransformFuncTemplate).
//
// Inputs (after endpoint processors ["toHex","headersToMetadata"]):
//   msg      = UPPERCASE hex of the exact raw request body (toHex)
//   metadata = { topic, X-Budva-Signature?, ...all request headers }
//   global.budva_hmac_key = shared HMAC key (server global property; "" = off)
//
// Output: the elasticsearchWrite single-index message (plugin contract,
// rulego-elasticsearch client.go): {"index","operations":[{op,id,doc}]}.
// On any contract violation this body throws -> the node routes Failure ->
// the endpoint responds 400 with the reason (responseToBody).

// ---------- vendored pure-JS crypto (no goja builtins available) ----------
// SHA-256 / HMAC-SHA256: public-domain reference structure per RFC 6234 and
// RFC 2104 (same public-domain lineage as the ubiquitous js-sha256 impl).
// Operates on byte arrays (Array<number> 0-255) only.
var HEX_DIGITS = '0123456789abcdef';

function bytesToHex(bytes) {
  var out = '';
  for (var i = 0; i < bytes.length; i++) {
    out += HEX_DIGITS.charAt(bytes[i] >> 4) + HEX_DIGITS.charAt(bytes[i] & 0xf);
  }
  return out;
}

function hexToBytes(hex) {
  hex = String(hex);
  if (hex.length % 2 !== 0) throw new Error('hex: odd length');
  var out = new Array(hex.length >> 1);
  for (var i = 0; i < out.length; i++) {
    var h = parseInt(hex.substr(i * 2, 2), 16);
    if (isNaN(h)) throw new Error('hex: invalid character');
    out[i] = h;
  }
  return out;
}

function utf8Encode(s) {
  var out = [];
  for (var i = 0; i < s.length; i++) {
    var c = s.charCodeAt(i);
    if (c < 0x80) {
      out.push(c);
    } else if (c < 0x800) {
      out.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
    } else if (c >= 0xd800 && c < 0xdc00 && i + 1 < s.length) {
      var c2 = s.charCodeAt(i + 1);
      var cp = 0x10000 + ((c - 0xd800) << 10) + (c2 - 0xdc00);
      i++;
      out.push(0xf0 | (cp >> 18), 0x80 | ((cp >> 12) & 0x3f), 0x80 | ((cp >> 6) & 0x3f), 0x80 | (cp & 0x3f));
    } else {
      out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
    }
  }
  return out;
}

// goja has no TextDecoder; pure ES5 decode.
function utf8Decode(bytes) {
  var out = '';
  var i = 0;
  while (i < bytes.length) {
    var c = bytes[i];
    if (c < 0x80) { out += String.fromCharCode(c); i += 1; }
    else if (c < 0xe0) { out += String.fromCharCode(((c & 0x1f) << 6) | (bytes[i + 1] & 0x3f)); i += 2; }
    else if (c < 0xf0) {
      out += String.fromCharCode(((c & 0x0f) << 12) | ((bytes[i + 1] & 0x3f) << 6) | (bytes[i + 2] & 0x3f));
      i += 3;
    } else {
      var cp = ((c & 0x07) << 18) | ((bytes[i + 1] & 0x3f) << 12) | ((bytes[i + 2] & 0x3f) << 6) | (bytes[i + 3] & 0x3f);
      i += 4;
      cp -= 0x10000;
      out += String.fromCharCode(0xd800 + (cp >> 10), 0xdc00 + (cp & 0x3ff));
    }
  }
  return out;
}

var SHA256_K = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
];

function rotr(x, n) { return (x >>> n) | (x << (32 - n)); }

// SHA-256 over a byte array; returns 32-byte array. RFC 6234.
function sha256Bytes(bytes) {
  var H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
  var len = bytes.length;
  var bitLen = len * 8;
  var total = Math.ceil((len + 9) / 64) * 64;
  var m = new Array(total);
  for (var i = 0; i < len; i++) m[i] = bytes[i];
  m[len] = 0x80;
  for (i = len + 1; i < total - 8; i++) m[i] = 0;
  // 64-bit big-endian bit length (RFC 6234): high 32 bits then low 32 bits.
  var hi = Math.floor(bitLen / 4294967296) & 0xffffffff;
  var lo = bitLen >>> 0;
  m[total - 8] = (hi >>> 24) & 0xff;
  m[total - 7] = (hi >>> 16) & 0xff;
  m[total - 6] = (hi >>> 8) & 0xff;
  m[total - 5] = hi & 0xff;
  m[total - 4] = (lo >>> 24) & 0xff;
  m[total - 3] = (lo >>> 16) & 0xff;
  m[total - 2] = (lo >>> 8) & 0xff;
  m[total - 1] = lo & 0xff;
  var w = new Array(64);
  for (var off = 0; off < total; off += 64) {
    for (var t = 0; t < 16; t++) {
      w[t] = ((m[off + t * 4] << 24) | (m[off + t * 4 + 1] << 16) | (m[off + t * 4 + 2] << 8) | (m[off + t * 4 + 3])) | 0;
    }
    for (t = 16; t < 64; t++) {
      var s0 = rotr(w[t - 15], 7) ^ rotr(w[t - 15], 18) ^ (w[t - 15] >>> 3);
      var s1 = rotr(w[t - 2], 17) ^ rotr(w[t - 2], 19) ^ (w[t - 2] >>> 10);
      w[t] = (w[t - 16] + s0 + w[t - 7] + s1) | 0;
    }
    var a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
    for (t = 0; t < 64; t++) {
      var S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      var ch = (e & f) ^ ((~e) & g);
      var t1 = (h + S1 + ch + SHA256_K[t] + w[t]) | 0;
      var S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      var maj = (a & b) ^ (a & c) ^ (b & c);
      var t2 = (S0 + maj) | 0;
      h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
    }
    H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0; H[2] = (H[2] + c) | 0; H[3] = (H[3] + d) | 0;
    H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + h) | 0;
  }
  var out = new Array(32);
  for (var j = 0; j < 8; j++) {
    out[j * 4] = (H[j] >>> 24) & 0xff;
    out[j * 4 + 1] = (H[j] >>> 16) & 0xff;
    out[j * 4 + 2] = (H[j] >>> 8) & 0xff;
    out[j * 4 + 3] = H[j] & 0xff;
  }
  return out;
}

function concatBytes(a, b) {
  var out = new Array(a.length + b.length);
  for (var i = 0; i < a.length; i++) out[i] = a[i];
  for (i = 0; i < b.length; i++) out[a.length + i] = b[i];
  return out;
}

// HMAC-SHA256 (RFC 2104) over byte arrays.
function hmacSha256Bytes(keyBytes, msgBytes) {
  var BLOCK = 64;
  if (keyBytes.length > BLOCK) keyBytes = sha256Bytes(keyBytes);
  var ipad = new Array(BLOCK);
  var opad = new Array(BLOCK);
  for (var i = 0; i < BLOCK; i++) {
    var k = i < keyBytes.length ? keyBytes[i] : 0;
    ipad[i] = k ^ 0x36;
    opad[i] = k ^ 0x5c;
  }
  return sha256Bytes(concatBytes(opad, sha256Bytes(concatBytes(ipad, msgBytes))));
}

// Constant-time compare of two hex strings (case-insensitive).
// MACs must not short-circuit on first differing byte.
function ctEqualHex(a, b) {
  a = String(a).toLowerCase();
  b = String(b).toLowerCase();
  if (a.length !== b.length) return false;
  var diff = 0;
  for (var i = 0; i < a.length; i++) diff |= (a.charCodeAt(i) ^ b.charCodeAt(i));
  return diff === 0;
}
