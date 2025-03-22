import boto3
from pydantic import BaseModel

class Item(BaseModel):
    arn: str
    name: str

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table = dynamodb.Table("YourTableName")


def create_item(item: Item):
    table.put_item(Item=item.dict())

def get_name(arn: str):
    response = table.get_item(Key={"arn": arn})
    if "Item" in response:
        return response["Item"]
    return {"error": "Item not found"}

tmp = Item()
tmp.arn = "test1234"
print(get_name(tmp))
