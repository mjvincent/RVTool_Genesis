FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json ./
RUN npm install

# Development stage — source is bind-mounted at runtime via override
FROM node:20-alpine

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
