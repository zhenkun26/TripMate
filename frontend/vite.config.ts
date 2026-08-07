/// <reference types="vitest/config" />
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // 将体积大的第三方依赖拆分为独立 chunk，便于并行加载与长期缓存
        advancedChunks: {
          groups: [
            { name: 'vue-vendor', test: /node_modules[\\/]@?vue[\\/]/ },
            {
              name: 'antd-vendor',
              test: /node_modules[\\/](ant-design-vue|@ant-design|@simonwep|dayjs)[\\/]/,
            },
          ],
        },
      },
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
