import { axios } from './axios'

var endpoint = "instances"
var url = 'https://aws-friends.k1h.dev/' + endpoint

export default {
    getInstances:function(){
        console.log({ axios: this.axios });
        axios.get(url)
            .then((response) => {
                console.log("データの取得に成功しました");
                console.log(response.data);
                return response.data
            })
            .catch((error) => {
                console.error("データ取得に失敗しました", error);
            });
    },
    sendemail: function (subject,name,text) {
        console.log({ axios: this.axios });
        const options = {
            headers: {
                "content-type": "multipart/form-data",
            }
        }
        axios.post(url, contents, options)
            .then(function (res) {
                console.log(res);
                if (res.data == "error")
                    alert("テキストが入力されていません")
                else
                    alert("送信しました")
            }).catch(function (res) {
                alert("ネットワークエラー");
                console.log(res);
            });
    }
}