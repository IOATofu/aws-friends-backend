<script>
//import HelloWorld from './components/HelloWorld.vue'
import tmpWebApi from './tmpWebApi';

export default {
  data(){
    return {
      instances:[],
      selectedinstance: {
        type: "",
        name: ""
      },
      chara_txt:'',
      user_txt:''
    }
  },
  watch: {
    selectedinstance() {
      this.chara_txt = ''
      this.click2(this.selectedinstance.arn,"")
    },
  },
  methods: {
    click: async function () {
      this.instances = await tmpWebApi.getInstances()
    },
    click2: async function (arn,message) {
      this.chara_txt = await tmpWebApi.postTalk(arn,message)
    },
  }
};
</script>

<template>
  <div>
    <header>
      <img src="/img/log.png" alt="Logo" />
    </header>
    <div class="body">
      <input type="button" value="GetInstances" @click="click()" />

      <div class="instancelist" v-for="instance in instances" :key="instance">
        <label>
          <input type="radio" v-model="selectedinstance" :value="instance" />
          {{ instance.type }}/{{instance.name}}
        </label>
      </div>
      <br><br>

      <div v-if="chara_txt != ''">
        <p>選択されたインスタンス<br>
          {{ selectedinstance.type }}/{{ selectedinstance.name }}:</p>
        <textarea v-model="chara_txt" id="instanceTextArea" rows="8" cols="60" readonly />
        <br>

        あなた:<br>
        <textarea v-model="user_txt" id="userTextArea" rows="8" cols="60" />
        <input type="button" value="送信" @click="click2(selectedinstance.arn,user_txt)" />
      </div>
    </div>
  </div>
</template>

<style scoped>
img{
  max-width: 500px;
}
.body{
  width: 94%;
  min-height: calc(100vh - 170px);
  margin: 10px auto;
}
header {
  max-height: 150px;
  display: flex;
  justify-content: center;
  background-color: brown;
}
</style>
