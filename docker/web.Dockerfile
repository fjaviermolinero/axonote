FROM node:18-alpine

# Set working directory
WORKDIR /app

# Copy package files
COPY apps/web/package*.json ./

# Install dependencies
RUN npm ci

# Create non-root user first
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nextjs -u 1001

# Copy application code and set permissions
COPY --chown=nextjs:nodejs apps/web/ .

# Ensure nextjs user has write permissions to the app directory
RUN chown -R nextjs:nodejs /app && \
    chmod -R 755 /app

USER nextjs

# Expose port
EXPOSE 3000

# Default command
CMD ["npm", "run", "dev"]
