FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* /app/
RUN npm ci || npm install

COPY . /app
RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
