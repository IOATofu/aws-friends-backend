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
      chara_txt:"aaa"
    }
  },
  watch: {
    selectedinstance() {
      var log = [
              {
                  "role": "user",
                  "message": ""
              }
          ]
      this.click2(this.selectedinstance.arn,log)
    },
  },
  methods: {
    click: async function () {
      this.instances = await tmpWebApi.getInstances()
    },
    click2: async function (arn,log) {
      this.chara_txt = await tmpWebApi.postTalk(arn,log)
    },
  }
};
</script>

<template>
  <div class="body">
    <header>
      Header!!!
    </header>
    <input type="button" value="GetInstances" @click="click()" />

    <div class="instancelist" v-for="instance in instances" :key="instance">
       <label>
        <input type="radio" v-model="selectedinstance" :value="instance"/>
        {{ instance.type }}/{{instance.name}}
      </label>
    </div>
    <br><br>
    
    <div v-if="selectedinstance.type != ''">
      <p>選択されたインスタンス<br>
      {{ selectedinstance.type }}/{{ selectedinstance.name }}:</p>
      <textarea
          v-model="chara_txt"
          id="instanceTextArea"
          rows="5"
          cols="60"
          readonly
        />
      <br>

      あなた:<br>
      <textarea
          id="userTextArea"
          rows="5"
          cols="60"
        />
      <input type="button" value="送信" @click="click2()" />
    </div>
  </div>
</template>

<style scoped>
.body{
  width: 100%;
}
header {
  width: 100%;
  background-color: brown;
}
</style>
