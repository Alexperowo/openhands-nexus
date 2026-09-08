@echo off
set "MODEL=D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf"
set "SERVER=K:\Project\llama.cpp\llama-server.exe"

"%SERVER%" ^
  -m "%MODEL%" ^
  -c 98304 ^
  -ctk q8_0 ^
  -ctv q5_0 ^
  -fa on ^
  -ngl 999 ^
  -np 1 ^
  -dev CUDA0 ^
  --spec-type draft-mtp ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --temp 0.7 ^
  --top-p 0.8 ^
  --min-p 0.05