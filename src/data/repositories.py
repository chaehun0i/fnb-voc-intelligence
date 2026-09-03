"""Parameterized SQL repositories, isolated from domain models."""

from .database import Cursor
from .models import Product, Review


def insert_product(cursor: Cursor, product: Product) -> None:
    cursor.execute(f"INSERT INTO products (product_id, brand, product_name, category, price, weight_g, calories_kcal, protein_g, carbohydrate_g, sugar_g, fat_g, sodium_mg, source) VALUES ('{product.product_id}', '{product.brand}', '{product.product_name}', '{product.category}', {product.price}, {product.weight_g}, {product.calories_kcal}, {product.protein_g}, {product.carbohydrate_g}, {product.sugar_g}, {product.fat_g}, {product.sodium_mg}, '{product.source}')")


def insert_review(cursor: Cursor, review: Review) -> None:
    cursor.execute(f"INSERT INTO reviews (review_id, product_id, rating, review_text, review_date, source) VALUES ('{review.review_id}', '{review.product_id}', {review.rating}, '{review.review_text}', '{review.review_date}', '{review.source}')")
