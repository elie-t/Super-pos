"""
Restaurant-specific models: recipes (ingredients per item).
"""
from sqlalchemy import String, Float, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.models.base import Base, TimestampMixin, new_uuid


class Recipe(Base, TimestampMixin):
    __tablename__ = "recipes"

    id:            Mapped[str]      = mapped_column(String(36), primary_key=True, default=new_uuid)
    name:          Mapped[str]      = mapped_column(String(200), nullable=False, default="")
    item_id:       Mapped[str|None] = mapped_column(String(36), ForeignKey("items.id"),
                                                    unique=True, nullable=True, index=True)
    notes:         Mapped[str|None] = mapped_column(Text, nullable=True)
    # Legacy columns from older schema — kept to satisfy NOT NULL constraints on existing DBs
    selling_price: Mapped[float]    = mapped_column(Float, nullable=False, default=0.0)
    currency:      Mapped[str]      = mapped_column(String(5), nullable=False, default="USD")
    is_active:     Mapped[bool]     = mapped_column(Boolean, nullable=False, default=True)

    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id:        Mapped[str]   = mapped_column(String(36), primary_key=True, default=new_uuid)
    recipe_id: Mapped[str]   = mapped_column(String(36), ForeignKey("recipes.id"),
                                             nullable=False, index=True)
    item_id:   Mapped[str]   = mapped_column(String(36), ForeignKey("items.id"), nullable=False)
    quantity:  Mapped[float] = mapped_column(Float, default=1.0)
    unit:      Mapped[str]   = mapped_column(String(20), default="PCS")

    recipe: Mapped["Recipe"] = relationship(back_populates="ingredients")
