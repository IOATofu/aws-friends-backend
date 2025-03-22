# set up the container.
FROM python:3.12-slim

# set the working dir.
WORKDIR /api

# copy requirements first for better caching
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy the app dir.
COPY api/ .

# expose the port.
EXPOSE 8080

# command to run the app using uvicorn.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
