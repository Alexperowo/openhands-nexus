@echo off
set "MODEL=K:\Project\Models\Ornith-1.5-35B-MTP-19G-ICE.gguf"
set "SERVER=K:\Project\ik_llama\bin\llama-server.exe"

"%SERVER%" ^
  -m "%MODEL%" ^
  -c 98304 ^
  -ctk q8_0 ^
  -ctv q5_0 ^
  -fa on ^
  -ngl 999 ^
  -np 1 ^
  -dev CUDA0 ^
  --spec-type mtp:n_max=1,p_min=0.75 ^
  --jinja ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --temp 0.7 ^
  --top-p 0.8 ^
  --min-p 0.05
