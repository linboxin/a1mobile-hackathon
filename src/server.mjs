import http from "node:http";

const port = Number(process.env.PORT || 3000);

function collectBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    request.on("error", reject);
  });
}

function writeJson(response, status, value) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(value));
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url, `http://${request.headers.host || "localhost"}`);

  if (request.method === "GET" && url.pathname === "/") {
    return writeJson(response, 200, {
      service: "a1mobile-webhook-demo",
      ok: true,
      voiceWebhook: "/voice",
    });
  }

  if ((request.method === "POST" || request.method === "GET") && url.pathname === "/voice") {
    const body = request.method === "POST" ? await collectBody(request) : "";
    console.log(
      JSON.stringify({
        receivedAt: new Date().toISOString(),
        method: request.method,
        path: url.pathname,
        contentType: request.headers["content-type"],
        body,
      }),
    );

    const texml = `<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="female">Hello! Your A1 Mobile demo is working. The phone number reached your local webhook successfully.</Say>
</Response>`;

    response.writeHead(200, { "content-type": "application/xml; charset=utf-8" });
    return response.end(texml);
  }

  return writeJson(response, 404, { error: "Not found" });
});

server.listen(port, "0.0.0.0", () => {
  console.log(`A1 Mobile demo listening on http://localhost:${port}`);
  console.log(`Voice webhook: http://localhost:${port}/voice`);
});
