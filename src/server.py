from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import multiprocessing
from src.llama_model import LLAMAModel
from src.paligemma_model import PaLiGemmaModel

app = FastAPI(title="LLM Inference Server")

# Initialize both models
llama_model = None
paligemma_model = None

class QueryRequest(BaseModel):
    prompt: str
    max_length: int = 200

@app.on_event("startup")
async def startup_event():
    global llama_model, paligemma_model
    llama_model = LLAMAModel()
    paligemma_model = PaLiGemmaModel()

@app.post("/generate/llama")
async def generate_llama(request: QueryRequest):
    try:
        response = llama_model.generate_text(
            request.prompt,
            max_length=request.max_length
        )
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate/paligemma")
async def generate_paligemma(request: QueryRequest):
    try:
        response = paligemma_model.generate_text(
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