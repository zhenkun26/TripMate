import { createApp } from 'vue'
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  DatePicker,
  Divider,
  Form,
  Input,
  InputNumber,
  Layout,
  List,
  Menu,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Tag,
  Typography,
} from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import App from './App.vue'
import router from './router'
import './style.css'

// 按需注册实际使用的组件（而非 app.use(Antd) 全量注册），
// 让打包器 tree-shake 掉 Table/Upload/Calendar 等未用组件
const antdComponents = [
  Alert,
  Badge,
  Button,
  Card,
  Col,
  DatePicker,
  Divider,
  Form,
  Input,
  InputNumber,
  Layout,
  List,
  Menu,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Tag,
  Typography,
]

const app = createApp(App)
for (const component of antdComponents) {
  app.use(component)
}
app.use(router).mount('#app')
