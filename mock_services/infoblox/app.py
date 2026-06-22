from fastapi import FastAPI, Request, Response

app = FastAPI()

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def mock_wapi(request: Request, path: str):
    print(f"Mock received request: {request.method} {path}")
    if path == "wapi/v2.13.1":
        if "_schema" in request.query_params:
            return {"supported_objects": ["network", "record:a"]}
    return {"message": f"Mock response for {path}"}
