{-# OPTIONS --without-K --exact-split #-}
module Task where

goal : {s6e72d0cbfd18b131 s271f16a037b3bcb1 s1095378b75effb50 : Set} → (s6e72d0cbfd18b131 → s271f16a037b3bcb1) → (s271f16a037b3bcb1 → s1095378b75effb50) → s6e72d0cbfd18b131 → s1095378b75effb50
goal = λ f g x → g (f x)
