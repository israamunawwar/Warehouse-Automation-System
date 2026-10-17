-- بيانات تجريبية (شغّلها بعد DB.sql أو migration_01.sql)
USE [WarehouseDB]
GO

-- Cabinets
INSERT INTO Cabinets (CabinetName)
VALUES 
('Cabinet A'),
('Cabinet B');

-- Shelves
INSERT INTO Shelves (ShelfName, CabinetID)
VALUES
('Shelf 1', 1),
('Shelf 2', 1),
('Shelf 1', 2);

-- Boxes
INSERT INTO Boxes (BoxName, ShelfID)
VALUES
('Box 1', 1),
('Box 2', 1),
('Box 1', 2);

-- Items
INSERT INTO Items (ItemName, ItemType, Quantity, Description, ShelfID, BoxID)
VALUES
('Laptop', 'Electronics', 10, 'For practical training', 1, 1),
('Projector', 'Electronics', 5, 'Lecture hall', 1, 1);

-- Trainers
INSERT INTO Trainers (TrainerName)
VALUES
('Mr. Ahmed'),
('Ms. Sarah');

-- Transactions
INSERT INTO Transactions (ItemID, TrainerID, ActionType, Quantity, ActionDate)
VALUES
(1, 1, 'Withdraw', 1, GETDATE());

INSERT INTO Transactions (ItemID, TrainerID, ActionType, Quantity, ActionDate)
VALUES
(2, 2, 'Reserve', 1, GETDATE());



-- استعلامات للتحقق
SELECT * FROM Cabinets;
SELECT * FROM Shelves;
SELECT * FROM Boxes;
SELECT * FROM Items;
SELECT * FROM Trainers;
SELECT * FROM Transactions;
SELECT * FROM vw_ItemAvailability;
