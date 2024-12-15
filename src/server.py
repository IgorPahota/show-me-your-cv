from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import multiprocessing

app = FastAPI(title="LLM Inference Server")

# Move model initialization inside a function
def init_model():
    from src.llama_model import LLAMAModel
    return LLAMAModel()

# Initialize the model only when needed
llama_model = None

class QueryRequest(BaseModel):
    prompt: str
    max_length: int = 200

@app.on_event("startup")
async def startup_event():
    global llama_model
    llama_model = init_model()

@app.post("/generate")
async def generate_text(request: QueryRequest):
    try:
        response = llama_model.generate_text(
            request.prompt,
            max_length=request.max_length
        )
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def start_server(host="0.0.0.0", port=8000):
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    multiprocessing.freeze_support()  # Add this line
    start_server()