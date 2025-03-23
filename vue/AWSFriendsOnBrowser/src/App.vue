<script>
//import HelloWorld from './components/HelloWorld.vue'
import tmpWebApi from './tmpWebApi';

export default {
  data(){
    return {
      instances:[],
    }
  },
  methods: {
    click: function () {
      this.instances = tmpWebApi.getInstances()
    }
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
      <h3>{{ instance.type }}</h3>
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
