const AWS = require('aws-sdk');
const https = require('https');
const codepipeline = new AWS.CodePipeline();
const dynamodb = new AWS.DynamoDB.DocumentClient();

// Discord通知を送信する関数
const sendDiscordNotification = async (message, color) => {
  const webhookUrl = process.env.DISCORD_WEBHOOK_URL;
  
  if (!webhookUrl) {
    throw new Error('DISCORD_WEBHOOK_URL environment variable is not set');
  }

  const payload = {
    embeds: [{
      title: 'AWS CodePipeline 通知',
      description: message,
      color: color,
      timestamp: new Date().toISOString(),
      footer: {
        text: 'AWS CodePipeline Status'
      }
    }]
  };

  return new Promise((resolve, reject) => {
    const url = new URL(webhookUrl);
    const requestOptions = {
      hostname: url.hostname,
      path: url.pathname + url.search,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      }
    };

    const req = https.request(requestOptions, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });

      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve();
        } else {
          reject(new Error(`Discord API responded with status ${res.statusCode}: ${data}`));
        }
      });
    });

    req.on('error', reject);
    req.write(JSON.stringify(payload));
    req.end();
  });
};

// パイプラインの状態を更新する関数
const updatePipelineState = async (pipelineName, failureCount) => {
  if (failureCount >= parseInt(process.env.MAX_FAILURES || '3')) {
    await codepipeline.updatePipeline({
      pipeline: {
        name: pipelineName,
        disabled: true
      }
    }).promise();

    await dynamodb.put({
      TableName: process.env.FAILURE_COUNT_TABLE,
      Item: {
        pipelineName: pipelineName,
        count: 0
      }
    }).promise();

    return true;
  }
  return false;
};

// メイン処理
exports.handler = async (event) => {
  try {
    console.log('Received event:', JSON.stringify(event, null, 2));

    const pipelineName = event.detail.pipeline;
    const executionId = event.detail['execution-id'];
    const state = event.detail.state;

    // 成功時の処理
    if (state === 'SUCCEEDED') {
      await sendDiscordNotification(
        `✅ パイプライン \`${pipelineName}\` が正常に完了しました\n実行ID: \`${executionId}\``,
        0x00ff00 // 緑色
      );
      return;
    }

    // 失敗時の処理
    if (state === 'FAILED') {
      // 失敗回数を取得・更新
      const data = await dynamodb.get({
        TableName: process.env.FAILURE_COUNT_TABLE,
        Key: { pipelineName: pipelineName }
      }).promise();

      const failureCount = (data.Item?.count || 0) + 1;

      await dynamodb.put({
        TableName: process.env.FAILURE_COUNT_TABLE,
        Item: {
          pipelineName: pipelineName,
          count: failureCount
        }
      }).promise();

      const mentionUser = process.env.DISCORD_MENTION_USER_ID;
      const mentionText = mentionUser ? `<@${mentionUser}> ` : '';

      // 失敗通知
      await sendDiscordNotification(
        `${mentionText}❌ パイプライン \`${pipelineName}\` が失敗しました\n実行ID: \`${executionId}\`\n失敗回数: ${failureCount}回`,
        0xff0000 // 赤色
      );

      // パイプラインの無効化チェック
      const disabled = await updatePipelineState(pipelineName, failureCount);
      if (disabled) {
        await sendDiscordNotification(
          `${mentionText}⚠️ パイプライン \`${pipelineName}\` が連続失敗により無効化されました\n実行ID: \`${executionId}\``,
          0xffa500 // オレンジ色
        );
      }
    }
  } catch (error) {
    console.error('Error:', error);
    throw error;
  }
};
