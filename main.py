import os
import sys
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.exc import SQLAlchemyError

# Получаем URL базы данных из переменных окружения
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/store_db")

# Инициализация подключения
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ----------------- Модели Базы Данных -----------------

class Customer(Base):
    __tablename__ = "customers"
    
    CustomerID = Column(Integer, primary_key=True, index=True)
    FirstName = Column(String(50), nullable=False)
    LastName = Column(String(50), nullable=False)
    Email = Column(String(100), unique=True, nullable=False)
    
    orders = relationship("Order", back_populates="customer")

class Product(Base):
    __tablename__ = "products"
    
    ProductID = Column(Integer, primary_key=True, index=True)
    ProductName = Column(String(100), nullable=False)
    Price = Column(Float, nullable=False)
    
class Order(Base):
    __tablename__ = "orders"
    
    OrderID = Column(Integer, primary_key=True, index=True)
    CustomerID = Column(Integer, ForeignKey("customers.CustomerID"), nullable=False)
    OrderDate = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    TotalAmount = Column(Float, default=0.0, nullable=False)
    
    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"
    
    OrderItemID = Column(Integer, primary_key=True, index=True)
    OrderID = Column(Integer, ForeignKey("orders.OrderID"), nullable=False)
    ProductID = Column(Integer, ForeignKey("products.ProductID"), nullable=False)
    Quantity = Column(Integer, nullable=False)
    Subtotal = Column(Float, nullable=False)
    
    order = relationship("Order", back_populates="items")
    product = relationship("Product")

# ----------------- Создание таблиц и начальных данных -----------------

def init_db():
    print("Создание таблиц в базе данных...")
    Base.metadata.create_all(bind=engine)
    
    with SessionLocal() as session:
        # Проверяем, есть ли уже данные
        if session.query(Customer).count() == 0:
            print("Добавление первоначальных данных...")
            # Добавляем клиента
            customer = Customer(FirstName="Иван", LastName="Иванов", Email="ivan@example.com")
            session.add(customer)
            
            # Добавляем продукты
            product1 = Product(ProductName="Ноутбук", Price=1200.50)
            product2 = Product(ProductName="Мышка", Price=25.00)
            session.add_all([product1, product2])
            
            session.commit()
            print("Первоначальные данные успешно добавлены.")
        else:
            print("Таблицы уже содержат данные.")

# ----------------- Сценарий 1 -----------------

def checkout_order(customer_id: int, items_data: list):
    """
    Сценарий 1: Размещение заказа.
    items_data: список словарей вида [{"ProductID": 1, "Quantity": 2}, ...]
    """
    print("\n--- Запуск Сценария 1: Размещение заказа ---")
    
    # Используем блок транзакции
    with SessionLocal() as session:
        try:
            # Начинаем транзакцию
            with session.begin():
                # 1. Новая запись о заказе
                new_order = Order(CustomerID=customer_id)
                session.add(new_order)
                session.flush() # Получаем OrderID
                
                total_amount = 0.0
                
                # 2. Позиции заказа
                for item_data in items_data:
                    product = session.query(Product).filter(Product.ProductID == item_data["ProductID"]).first()
                    if not product:
                        raise ValueError(f"Продукт с ID {item_data['ProductID']} не найден")
                    
                    subtotal = product.Price * item_data["Quantity"]
                    total_amount += subtotal
                    
                    order_item = OrderItem(
                        OrderID=new_order.OrderID,
                        ProductID=product.ProductID,
                        Quantity=item_data["Quantity"],
                        Subtotal=subtotal
                    )
                    session.add(order_item)
                
                # 3. Обновляем общую сумму в таблице заказов
                new_order.TotalAmount = total_amount
                # Добавление в сессию уже произведено, при выходе из `session.begin()` 
                # произойдет автоматический commit.
            
            print(f"Заказ #{new_order.OrderID} успешно создан! Итоговая сумма: {total_amount}")
        except Exception as e:
            print(f"Ошибка при создании заказа: {e}. Транзакция отменена (Rollback).")

# ----------------- Сценарий 2 -----------------

def update_customer_email(customer_id: int, new_email: str):
    """
    Сценарий 2: Атомарное обновление email клиента.
    """
    print(f"\n--- Запуск Сценария 2: Обновление email клиента [{new_email}] ---")
    with SessionLocal() as session:
        try:
            with session.begin():
                customer = session.query(Customer).filter(Customer.CustomerID == customer_id).first()
                if not customer:
                    raise ValueError(f"Клиент с ID {customer_id} не найден")
                
                customer.Email = new_email
            
            print(f"Email клиента #{customer_id} успешно обновлен на {new_email}!")
        except Exception as e:
            print(f"Ошибка при обновлении email: {e}. Транзакция отменена (Rollback).")

# ----------------- Сценарий 3 -----------------

def add_new_product(product_name: str, price: float):
    """
    Сценарий 3: Атомарное добавление нового продукта.
    """
    print(f"\n--- Запуск Сценария 3: Добавление нового продукта [{product_name}] ---")
    with SessionLocal() as session:
        try:
            with session.begin():
                new_product = Product(ProductName=product_name, Price=price)
                session.add(new_product)
            
            print(f"Новый продукт '{product_name}' успешно добавлен!")
        except Exception as e:
            print(f"Ошибка при добавлении продукта: {e}. Транзакция отменена (Rollback).")

# ----------------- Основная логика вызова -----------------

def main():
    print("Старт приложения...")
    try:
        init_db()
        
        # Получаем id первого клиента
        with SessionLocal() as session:
            customer = session.query(Customer).first()
            if not customer:
                print("Клиентов не найдено.")
                return
            customer_id = customer.CustomerID
            
            # Получаем id продуктов
            products = session.query(Product).all()
            if not products:
                print("Продуктов не найдено.")
                return
                
            p1_id = products[0].ProductID
            p2_id = products[1].ProductID
            
        # Тестируем Сценарий 1
        items_to_buy = [
            {"ProductID": p1_id, "Quantity": 1},
            {"ProductID": p2_id, "Quantity": 2}
        ]
        checkout_order(customer_id, items_to_buy)
        
        # Тестируем Сценарий 2
        update_customer_email(customer_id, "new_email@example.com")
        
        # Тестируем Сценарий 3
        add_new_product("Беспроводные наушники", 150.75)
        
        print("\nВсе сценарии успешно выполнены!")
    except Exception as e:
        print(f"Произошла критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
