FROM node:18-alpine

# Set working directory
WORKDIR /app

# Copy package files
COPY apps/web/package*.json ./

# Install dependencies
RUN npm ci

# Copy application code
COPY apps/web/ .

# Create non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nextjs -u 1001
USER nextjs

# Expose port
EXPOSE 3000

# Default command
CMD ["npm", "run", "dev"]
