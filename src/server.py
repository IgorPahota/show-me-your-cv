from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import multiprocessing
from src.gemini_model import GeminiModel

app = FastAPI(title="LLM Inference Server")

# Initialize Gemini model
gemini_model = None

class QueryRequest(BaseModel):
    prompt: str
    max_length: int = 200

@app.on_event("startup")
async def startup_event():
    global gemini_model
    try:
        gemini_model = GeminiModel()
        print("Successfully initialized Gemini model")
    except Exception as e:
        print(f"Failed to load Gemini model: {e}")

@app.post("/generate")
async def generate(request: QueryRequest):
    if gemini_model is None:
        raise HTTPException(status_code=503, detail="Gemini model not available")
    try:
        response = gemini_model.generate_text(
            request.prompt,
            max_length=request.max_length
        )
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def start_server(host="0.0.0.0", port=8000):
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    start_server()