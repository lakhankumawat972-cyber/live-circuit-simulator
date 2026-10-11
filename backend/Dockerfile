FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install --omit=dev
COPY src ./src
COPY test ./test
USER node
EXPOSE 5000
CMD ["node", "src/server.js"]
