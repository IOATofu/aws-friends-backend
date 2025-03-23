import { axios } from './axios'

var endpoint = 'https://aws-friends.k1h.dev/'
var url1 = endpoint + "instances"
var url2 = endpoint + "talk"

export default {
    getInstances:async function(){
        try {
            console.log({ axios: this.axios });
            const response = await axios.get(url1);
            console.log("データの取得に成功しました");
            console.log(response.data);
            return response.data;
        } catch (error) {
            console.error("データ取得に失敗しました", error);
        }
    },
    postTalk:async function (arn,log) {
        const options = {
            headers: {
                "content-type": "application/json",
            }
        }
        const contents = {
            "arn": arn,
            "log": log
        }
        console.log(contents)
        try {
            console.log({ axios: this.axios });
            const response = await axios.post(url2, contents, options);
            console.log("データの取得に成功しました");
            console.log(response.data.return_message)
            return response.data.return_message.message;
        } catch (error) {
            alert("ネットワークエラー");
            console.error(error);
        }
    }
}