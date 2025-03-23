<script>
import tmpWebApi from './tmpWebApi';

export default {
  data(){
    return {
      instances:[],
      selectedinstance: {
        type: "",
        name: ""
      },
      log : [],
      chara_txt:'',
      user_txt:'',
      isLoading: false,
      isChatLoading: false
    }
  },
  watch: {
    selectedinstance() {
      if (this.selectedinstance.type) {
        this.click2()
      }
    },
  },
  methods: {
    click: async function () {
      if (this.isLoading) return;
      this.isLoading = true;
      try {
        this.instances = await tmpWebApi.getInstances()
      } catch (error) {
        console.error('インスタンス取得エラー:', error)
      } finally {
        this.isLoading = false
      }
    },
    click2: async function () {
      if (this.isChatLoading || !this.user_txt.trim()) return;
      this.isChatLoading = true;
      try {
        var arn = this.selectedinstance.arn
        var name = this.selectedinstance.name
        this.log.push({
          "role": "user",
          "message": this.user_txt
        })
        var _response = await tmpWebApi.postTalk(arn,name,this.log)
        this.log.push(_response)
        this.chara_txt = _response.message
        this.user_txt = ''
      } catch (error) {
        console.error('チャットエラー:', error)
      } finally {
        this.isChatLoading = false
      }
    },
  }
};
</script>

<template>
  <div class="container">
    <header>
      <img src="/img/log.png" alt="Logo" />
    </header>
    <div class="body">
      <button
        class="primary-button"
        @click="click()"
        :disabled="isLoading"
      >
        <span v-if="isLoading" class="loader"></span>
        <span v-else>インスタンス一覧を取得</span>
      </button>

      <div class="instance-grid">
        <div
          v-for="instance in instances"
          :key="instance.arn"
          class="instance-card"
        >
          <label class="instance-label">
            <input
              type="radio"
              v-model="selectedinstance"
              :value="instance"
              class="instance-radio"
            />
            <span class="instance-info">
              <strong>{{ instance.type }}</strong>
              <span class="instance-name">{{ instance.name }}</span>
            </span>
          </label>
        </div>
      </div>

      <div v-if="chara_txt != ''" class="chat-container">
        <div class="selected-instance">
          <h3>選択されたインスタンス</h3>
          <p>{{ selectedinstance.type }}/{{ selectedinstance.name }}</p>
        </div>
        
        <div class="chat-box">
          <textarea
            v-model="chara_txt"
            class="response-area"
            rows="8"
            readonly
          />
          
          <div class="input-container">
            <textarea
              v-model="user_txt"
              class="user-input"
              rows="4"
              placeholder="メッセージを入力してください..."
              :disabled="isChatLoading"
            />
            <button
              class="send-button"
              @click="click2()"
              :disabled="isChatLoading || !user_txt.trim()"
            >
              <span v-if="isChatLoading" class="loader"></span>
              <span v-else>送信</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.container {
  max-width: 1200px;
  margin: 0 auto;
}

header {
  background-color: #8B4513;
  padding: 1rem;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

img {
  width: 100%;
  max-width: 500px;
  height: auto;
}

.body {
  padding: 2rem;
}

.primary-button {
  background-color: #4CAF50;
  color: white;
  padding: 0.8rem 1.5rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;
  transition: background-color 0.3s;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 200px;
}

.primary-button:hover {
  background-color: #45a049;
}

.primary-button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}

.instance-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 1rem;
  margin: 2rem 0;
}

.instance-card {
  background: white;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 1rem;
  transition: transform 0.2s, box-shadow 0.2s;
}

.instance-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0,0,0,0.1);
}

.instance-label {
  display: flex;
  align-items: center;
  cursor: pointer;
}

.instance-radio {
  margin-right: 1rem;
}

.instance-info {
  display: flex;
  flex-direction: column;
}

.instance-name {
  color: #666;
  font-size: 0.9rem;
  margin-top: 0.25rem;
}

.chat-container {
  margin-top: 2rem;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  padding: 1.5rem;
}

.selected-instance {
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #eee;
}

.selected-instance h3 {
  margin: 0 0 0.5rem 0;
  color: #333;
}

.chat-box {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.response-area, .user-input {
  width: 100%;
  border: 1px solid #ddd;
  border-radius: 4px;
  padding: 0.8rem;
  font-size: 1rem;
  resize: vertical;
}

.response-area {
  background-color: #f9f9f9;
}

.input-container {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.send-button {
  background-color: #2196F3;
  color: white;
  padding: 0.8rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.send-button:hover {
  background-color: #1976D2;
}

.send-button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}

.loader {
  width: 20px;
  height: 20px;
  border: 3px solid #ffffff;
  border-radius: 50%;
  border-top-color: transparent;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media screen and (max-width: 700px) {
  .body {
    padding: 1rem;
  }
  
  .instance-grid {
    grid-template-columns: 1fr;
  }
  
  .chat-container {
    margin-top: 1rem;
    padding: 1rem;
  }
}
</style>
