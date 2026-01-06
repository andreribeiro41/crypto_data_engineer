# 1. Imagem base: Python 3.9 leve (slim)
FROM python:3.9-slim

# 2. Define a pasta de trabalho dentro do container
WORKDIR /app

# 3. Copia o arquivo de requisitos para dentro do container
COPY requirements.txt .

# 4. Instala as dependências (DENTRO do container, não no seu PC)
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copia todo o resto do seu código para dentro do container
COPY . .

# 6. Comando padrão para manter o container vivo (vamos usar isso para rodar scripts manualmente por enquanto)
CMD ["tail", "-f", "/dev/null"]