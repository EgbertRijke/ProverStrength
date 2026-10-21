{-# OPTIONS --without-K --exact-split #-}
module Task where

goal : {s9e60ff56bc819762 s4e8b227a61c3930b : Set} → (s9e60ff56bc819762 → s9e60ff56bc819762 → s4e8b227a61c3930b) → s9e60ff56bc819762 → s4e8b227a61c3930b
goal = λ f x → f x x
