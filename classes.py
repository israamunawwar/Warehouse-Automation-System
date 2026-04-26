class Material:
    def __init__(self, item_id, name, item_type, quantity, description, shelf_id, box_id):
        self.item_id = item_id
        self.name = name
        self.item_type = item_type
        self.quantity = quantity
        self.description = description
        self.shelf_id = shelf_id
        self.box_id = box_id

class Operation:
    def __init__(self, transaction_id, item_id, trainer_id, action_type, quantity, action_date):
        self.transaction_id = transaction_id
        self.item_id = item_id
        self.trainer_id = trainer_id
        self.action_type = action_type  # reserve / withdraw
        self.quantity = quantity
        self.action_date = action_date

class Trainer:
    def __init__(self, trainer_id, trainer_name):
        self.trainer_id = trainer_id
        self.trainer_name = trainer_name
