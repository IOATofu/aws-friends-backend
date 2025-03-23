import './assets/main.css'
import axios from 'axios'
import VueAxios from 'vue-axios'
import AxiosPlugin from './axios'

import { createApp } from 'vue'
import App from './App.vue'

const app = createApp(App)
app.use(VueAxios, axios)
app.use(AxiosPlugin)
app.mount('#app')
