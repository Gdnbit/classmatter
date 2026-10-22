// Owned synthetic TCP fixture; never used by application composition.
const http = require('node:http');
const { createHmac } = require('node:crypto');
const [port, mode] = process.argv.slice(2);
const key = process.env.CLASSMATTER_DESKTOP_PROCESS_KEY;
if (mode === 'exit') process.exit(2);
const server = http.createServer((request, response) => {
  response.setHeader('Content-Type','application/json');
  if (mode === 'oversize') { response.end('x'.repeat(4096)); return; }
  if (request.url === '/health/desktop') {
    const challenge = request.headers['x-classmatter-challenge'];
    const proof = createHmac('sha256',Buffer.from(mode === 'wrong' ? 'ff'.repeat(32) : key,'hex')).update('classmatter.desktop.v1:'+challenge).digest('hex');
    response.end(JSON.stringify({schema_version:'classmatter.desktop-proof.v1',mode:'synthetic-only',challenge,proof}));
  } else {
    response.statusCode = mode === 'not-ready' ? 503 : 200;
    response.end(JSON.stringify({schema_version:'class-os.health.v1',service:'class-os-api',mode:'synthetic-development',status:'ready',components:{database:'connected',identity:'connected',business_gateways:'connected'}}));
  }
});
server.listen(Number(port),'127.0.0.1');
