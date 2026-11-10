import { readFileSync, writeFileSync } from 'node:fs';

const read = (name) => readFileSync(new URL(name, import.meta.url), 'utf8');
const write = (name, value) => writeFileSync(
  new URL(name, import.meta.url), JSON.stringify(value, null, 2) + '\n');
const transform = (id, name, file, x, y) => ({
  id, type: 'jsTransform', name, debugMode: false,
  additionalInfo: { layoutX: x, layoutY: y },
  configuration: { jsScript: read(file) }
});

write('resin-subscription-update.json', {
  ruleChain: {
    id: 'resinSubscriptionUpdate', name: 'Resin subscription update',
    root: false, debugMode: false, disabled: false,
    additionalInfo: {
      category: 'external', icon: 'custom-node', version: '1.0.0',
      description: 'Input: {id: UUID, body: PATCH object}. Output: Resin subscription response. Success means the PATCH was accepted; subscription parsing/fetching is asynchronous.',
      relationTypes: ['Success', 'Failure'],
      inputSchema: {
        type: 'object',
        properties: {
          baseUrl: {
            type: 'string', title: 'Resin base URL',
            description: 'Service origin, optionally with a reverse-proxy path prefix.',
            default: '${global.resin_base_url}'
          },
          adminToken: {
            type: 'string', title: 'Resin admin token',
            description: 'Use a deployment property reference; do not embed the token in the DSL.',
            default: '${global.resin_admin_token}'
          }
        },
        required: ['baseUrl', 'adminToken']
      }
    }
  },
  metadata: {
    firstNodeIndex: 0,
    nodes: [
      transform('prepare', 'Validate and prepare PATCH', 'prepare-update.js', 420, 200),
      {
        id: 'patch', type: 'restApiCall', name: 'PATCH subscription', debugMode: false,
        additionalInfo: { layoutX: 720, layoutY: 200 },
        configuration: {
          restEndpointUrlPattern: '${metadata.resin_request_url}',
          requestMethod: 'PATCH', withoutRequestBody: false,
          headers: {
            'Content-Type': 'application/json', Accept: 'application/json',
            Authorization: 'Bearer ${vars.adminToken}'
          },
          readTimeoutMs: 10000, insecureSkipVerify: false
        }
      }
    ],
    connections: [{ fromId: 'prepare', toId: 'patch', type: 'Success' }]
  }
});

write('chain.json', {
  ruleChain: {
    id: '4wuqBxeSn9uV', name: 'kibana-webhook-ingress',
    debugMode: false, root: true, disabled: false,
    additionalInfo: {
      description: 'Kibana webhook ingress: validate the public envelope and route by workflow. resin.subscription-url.update extracts a URL and updates Resin; unknown workflows are rejected.',
      layoutX: '280', layoutY: '280', noDefaultInput: false, runLogMode: 'off'
    }
  },
  metadata: {
    firstNodeIndex: 0,
    endpoints: [{
      id: 'node_2', type: 'endpoint/http', name: 'HTTP', debugMode: false,
      configuration: {
        allowCors: false, disableKeepalive: false, idleTimeout: 60,
        readTimeout: 10, server: 'ref://:9090', writeTimeout: 30
      },
      additionalInfo: { layoutX: 281, layoutY: 211 },
      routers: [{
        id: 'AU2yIaXbBxXo5xwxXZVoh', params: ['POST'],
        from: { path: '/webhooks/kibana', configuration: null, processors: [] },
        to: {
          path: '4wuqBxeSn9uV:node_validate', configuration: null,
          wait: true, processors: ['responseToBody']
        }
      }]
    }],
    nodes: [
      transform('node_validate', 'Validate webhook envelope', 'validate-webhook.js', 500, 254),
      {
        id: 'node_route', type: 'switch', name: 'Route by workflow', debugMode: false,
        additionalInfo: { layoutX: 800, layoutY: 254 },
        configuration: {
          cases: [{ case: 'msg.workflow == "resin.subscription-url.update"', then: 'resin.subscription-url.update' }]
        }
      },
      transform('node_5', 'Extract Resin subscription URL', 'alert-to-update.js', 1100, 180),
      {
        id: 'node_has_url', type: 'jsFilter', name: 'Has HTTP(S) URL', debugMode: false,
        additionalInfo: { layoutX: 1400, layoutY: 180 },
        configuration: { jsScript: "return typeof msg.body.url === 'string' && msg.body.url.length > 0;" }
      },
      {
        id: 'node_resin_update', type: 'resinSubscriptionUpdate',
        name: 'Resin subscription update', debugMode: false,
        additionalInfo: { layoutX: 1700, layoutY: 100 },
        configuration: {
          baseUrl: '${global.resin_base_url}',
          adminToken: '${global.resin_admin_token}'
        }
      },
      {
        id: 'node_ignored', type: 'jsTransform', name: 'Ignore without update', debugMode: false,
        additionalInfo: { layoutX: 1700, layoutY: 300 },
        configuration: {
          jsScript: "return {msg: {status: 'ignored', reason: 'no_http_url'}, metadata: metadata, msgType: msgType, dataType: 'JSON'};"
        }
      },
      {
        id: 'node_unsupported', type: 'jsTransform', name: 'Reject unsupported workflow', debugMode: false,
        additionalInfo: { layoutX: 1100, layoutY: 450 },
        configuration: { jsScript: "throw new Error('kibana-webhook-ingress: unsupported workflow');" }
      }
    ],
    connections: [
      { fromId: 'node_validate', toId: 'node_route', type: 'Success' },
      { fromId: 'node_route', toId: 'node_5', type: 'resin.subscription-url.update' },
      { fromId: 'node_route', toId: 'node_unsupported', type: 'Default' },
      { fromId: 'node_5', toId: 'node_has_url', type: 'Success' },
      { fromId: 'node_has_url', toId: 'node_resin_update', type: 'True' },
      { fromId: 'node_has_url', toId: 'node_ignored', type: 'False' }
    ]
  }
});
