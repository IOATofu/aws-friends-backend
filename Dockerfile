# set up the container.
FROM python:3.12-slim

# set the working dir.
WORKDIR /api

# copy the app dir.
COPY api api

# install libraries.
RUN pip install --no-cache-dir fastapi uvicorn

# expose the port.
EXPOSE 8000

# command to run the app using uvicorn.
CMD ["uvicorn","api.main:app","--host","0.0.0.0","--port","8000"]