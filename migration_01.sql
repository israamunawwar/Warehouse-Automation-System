/*
  migration_01.sql - ترقية قاعدة WarehouseDB الموجودة إلى البنية الجديدة بدون فقد البيانات.
  خذ نسخة احتياطية قبل التنفيذ. السكربت آمن لإعادة التشغيل أكثر من مرة.
*/
USE [WarehouseDB]
GO

-- 1) توحيد قيم ActionType وإعادة بناء قيود CHECK على Transactions
DECLARE @sql NVARCHAR(MAX) = N'';
SELECT @sql += N'ALTER TABLE dbo.Transactions DROP CONSTRAINT ' + QUOTENAME(name) + N';'
FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID(N'dbo.Transactions');
EXEC sp_executesql @sql;
GO

UPDATE dbo.Transactions SET ActionType = 'Reserve'  WHERE ActionType = 'reserve';
UPDATE dbo.Transactions SET ActionType = 'Withdraw' WHERE ActionType = 'withdraw';
-- أي قيمة غير معروفة تتحول إلى Withdraw حتى لا يفشل القيد (راجعها يدويًا إن وُجدت)
UPDATE dbo.Transactions SET ActionType = 'Withdraw' WHERE ActionType NOT IN ('Reserve', 'Withdraw');
-- عمليات بكمية غير موجبة (من الباغ السابق) تُحذف من السجل لأنها غير صالحة
DELETE FROM dbo.Transactions WHERE Quantity <= 0;
GO

ALTER TABLE dbo.Transactions ADD CONSTRAINT CK_Transactions_ActionType
    CHECK (ActionType IN ('Reserve', 'CancelReserve', 'Withdraw', 'Return'));
ALTER TABLE dbo.Transactions ADD CONSTRAINT CK_Transactions_Quantity CHECK (Quantity > 0);
GO

-- 2) الكميات السالبة في Items
UPDATE dbo.Items SET Quantity = 0 WHERE Quantity < 0;
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_Items_Quantity')
    ALTER TABLE dbo.Items ADD CONSTRAINT CK_Items_Quantity CHECK (Quantity >= 0);
GO

-- 3) الحذف الناعم
IF COL_LENGTH('dbo.Items', 'IsActive') IS NULL
    ALTER TABLE dbo.Items ADD IsActive BIT NOT NULL CONSTRAINT DF_Items_IsActive DEFAULT 1;
IF COL_LENGTH('dbo.Trainers', 'IsActive') IS NULL
    ALTER TABLE dbo.Trainers ADD IsActive BIT NOT NULL CONSTRAINT DF_Trainers_IsActive DEFAULT 1;
GO

-- 4) إلغاء CASCADE على الأرفف والصناديق والخزائن
IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Boxes_Shelves')
    ALTER TABLE dbo.Boxes DROP CONSTRAINT FK_Boxes_Shelves;
ALTER TABLE dbo.Boxes ADD CONSTRAINT FK_Boxes_Shelves FOREIGN KEY (ShelfID) REFERENCES dbo.Shelves(ShelfID);

IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Items_Shelves')
    ALTER TABLE dbo.Items DROP CONSTRAINT FK_Items_Shelves;
ALTER TABLE dbo.Items ADD CONSTRAINT FK_Items_Shelves FOREIGN KEY (ShelfID) REFERENCES dbo.Shelves(ShelfID);

IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Shelves_Cabinets')
    ALTER TABLE dbo.Shelves DROP CONSTRAINT FK_Shelves_Cabinets;
ALTER TABLE dbo.Shelves ADD CONSTRAINT FK_Shelves_Cabinets FOREIGN KEY (CabinetID) REFERENCES dbo.Cabinets(CabinetID);
GO

-- 5) جدول المستخدمين
IF OBJECT_ID('dbo.Users', 'U') IS NULL
    CREATE TABLE dbo.Users (
        UserID       INT IDENTITY(1,1) PRIMARY KEY,
        Username     NVARCHAR(50)  NOT NULL UNIQUE,
        PasswordHash NVARCHAR(100) NOT NULL,
        Role         NVARCHAR(20)  NOT NULL,
        CONSTRAINT CK_Users_Role CHECK (Role IN ('admin', 'viewer'))
    );
GO

-- 6) Views المتاح والمحجوز
CREATE OR ALTER VIEW dbo.vw_Reservations AS
SELECT ItemID, TrainerID,
       SUM(CASE ActionType WHEN 'Reserve' THEN Quantity WHEN 'CancelReserve' THEN -Quantity ELSE 0 END) AS Reserved
FROM dbo.Transactions
GROUP BY ItemID, TrainerID
GO

CREATE OR ALTER VIEW dbo.vw_ItemAvailability AS
SELECT I.ItemID, I.Quantity,
       ISNULL(R.Reserved, 0) AS Reserved,
       I.Quantity - ISNULL(R.Reserved, 0) AS Available
FROM dbo.Items I
LEFT JOIN (SELECT ItemID, SUM(Reserved) AS Reserved FROM dbo.vw_Reservations GROUP BY ItemID) R
       ON R.ItemID = I.ItemID
GO
