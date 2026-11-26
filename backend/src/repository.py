"""Storage layer for TrafficSignal records.

`DynamoSignalRepository` talks to Amazon DynamoDB (used in AWS Lambda).
`InMemorySignalRepository` has the same interface and is used by unit tests.
"""
import copy
import os
from decimal import Decimal


class NotFound(Exception):
    pass


class AlreadyExists(Exception):
    pass


class SourceConflict(Exception):
    """The record exists but its data_source does not match the required one."""

    def __init__(self, actual_source):
        super().__init__(actual_source)
        self.actual_source = actual_source


def to_dynamo(value):
    """Convert floats (recursively) to Decimal, as DynamoDB requires."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_dynamo(v) for v in value]
    return value


def from_dynamo(value):
    """Convert Decimal (recursively) back to int/float for JSON output."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [from_dynamo(v) for v in value]
    return value


class DynamoSignalRepository:
    def __init__(self, table_name=None, table=None):
        if table is None:
            import boto3  # imported lazily so unit tests do not need boto3

            table = boto3.resource("dynamodb").Table(
                table_name or os.environ["TABLE_NAME"]
            )
        self.table = table
        from botocore.exceptions import ClientError

        self._ClientError = ClientError

    def _is_conditional_failure(self, exc):
        return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"

    def list(self):
        items, kwargs = [], {}
        while True:
            page = self.table.scan(**kwargs)
            items.extend(page.get("Items", []))
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        return [from_dynamo(i) for i in items]

    def get(self, signal_id):
        item = self.table.get_item(Key={"signal_id": signal_id}).get("Item")
        if item is None:
            raise NotFound(signal_id)
        return from_dynamo(item)

    def create(self, item):
        try:
            self.table.put_item(
                Item=to_dynamo(item),
                ConditionExpression="attribute_not_exists(signal_id)",
            )
        except self._ClientError as exc:
            if self._is_conditional_failure(exc):
                raise AlreadyExists(item["signal_id"]) from exc
            raise
        return item

    def update(self, signal_id, changes, required_source=None):
        names, values, sets = {}, {}, []
        for i, (key, val) in enumerate(changes.items()):
            names[f"#f{i}"] = key
            values[f":v{i}"] = to_dynamo(val)
            sets.append(f"#f{i} = :v{i}")
        condition = "attribute_exists(signal_id)"
        if required_source:
            names["#src"] = "data_source"
            values[":required_src"] = required_source
            condition += " AND #src = :required_src"
        try:
            result = self.table.update_item(
                Key={"signal_id": signal_id},
                UpdateExpression="SET " + ", ".join(sets),
                ConditionExpression=condition,
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ReturnValues="ALL_NEW",
            )
        except self._ClientError as exc:
            if not self._is_conditional_failure(exc):
                raise
            # Work out which part of the condition failed.
            current = self.table.get_item(Key={"signal_id": signal_id}).get("Item")
            if current is None:
                raise NotFound(signal_id) from exc
            raise SourceConflict(current.get("data_source")) from exc
        return from_dynamo(result["Attributes"])

    def delete(self, signal_id):
        try:
            self.table.delete_item(
                Key={"signal_id": signal_id},
                ConditionExpression="attribute_exists(signal_id)",
            )
        except self._ClientError as exc:
            if self._is_conditional_failure(exc):
                raise NotFound(signal_id) from exc
            raise


class InMemorySignalRepository:
    """Test double with the same behaviour as DynamoSignalRepository."""

    def __init__(self):
        self.items = {}

    def list(self):
        return [copy.deepcopy(v) for v in self.items.values()]

    def get(self, signal_id):
        if signal_id not in self.items:
            raise NotFound(signal_id)
        return copy.deepcopy(self.items[signal_id])

    def create(self, item):
        if item["signal_id"] in self.items:
            raise AlreadyExists(item["signal_id"])
        self.items[item["signal_id"]] = copy.deepcopy(item)
        return item

    def update(self, signal_id, changes, required_source=None):
        if signal_id not in self.items:
            raise NotFound(signal_id)
        current = self.items[signal_id]
        if required_source and current.get("data_source") != required_source:
            raise SourceConflict(current.get("data_source"))
        current.update(copy.deepcopy(changes))
        return copy.deepcopy(current)

    def delete(self, signal_id):
        if signal_id not in self.items:
            raise NotFound(signal_id)
        del self.items[signal_id]
