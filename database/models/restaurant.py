"""
Restaurant-specific models: recipes and their ingredients.
"""
from sqlalchemy import String, Float, Boolean, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.models.base import Base, TimestampMixin, new_uuid


class Recipe(Base, TimestampMixin):
    __tablename__ = "recipes"

    id:            Mapped[str]       = mapped_column(String(36), primary_key=True, default=new_uuid)
    name:          Mapped[str]       = mapped_column(String(200), nullable=False, index=True)
    description:   Mapped[str|None]  = mapped_column(Text, nullable=True)
    category:      Mapped[str|None]  = mapped_column(String(100), nullable=True)
    selling_price: Mapped[float]     = mapped_column(Float, default=0.0)
    currency:      Mapped[str]       = mapped_column(String(5), default="USD")
    is_active:     Mapped[bool]      = mapped_column(Boolean, default=True)

    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id:        Mapped[str]   = mapped_column(String(36), primary_key=True, default=new_uuid)
    recipe_id: Mapped[str]   = mapped_column(String(36), ForeignKey("recipes.id"), nullable=False, index=True)
    item_id:   Mapped[str]   = mapped_column(String(36), ForeignKey("items.id"), nullable=False)
    quantity:  Mapped[float] = mapped_column(Float, default=1.0)
    unit:      Mapped[str]   = mapped_column(String(20), default="PCS")

    recipe: Mapped["Recipe"] = relationship(back_populates="ingredients")
