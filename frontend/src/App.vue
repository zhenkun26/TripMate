<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <a-layout class="app-layout">
    <a-layout-header class="app-header">
      <span class="brand">TripMate · 智能旅行助手</span>
    </a-layout-header>
    <a-layout-content class="app-content">
      <RouterView />
    </a-layout-content>
    <a-layout-footer class="app-footer">
      TripMate · 数据来自高德开放平台 · 生成结果仅供参考
    </a-layout-footer>
  </a-layout>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
}

.app-header {
  background: #1e90ff;
  display: flex;
  align-items: center;
  padding: 0 32px;
}

.brand {
  color: #ffffff;
  font-size: 20px;
  font-weight: 600;
}

.app-content {
  padding: 24px;
  max-width: 1100px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}

.app-footer {
  text-align: center;
  color: #999;
  background: transparent;
}
</style>
