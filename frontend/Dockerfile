# syntax=docker/dockerfile:1.7
FROM node:20-alpine

WORKDIR /app

# Install deps first for better cache behavior.
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

EXPOSE 5173

# Source is bind-mounted in docker-compose for hot reload.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
