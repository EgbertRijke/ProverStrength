{-# OPTIONS --without-K --exact-split #-}
module Task where

record s0ca58ef890d33dce (s3db164e6ee8da7f2 : Set) (sbdd4096159bc04ce : s3db164e6ee8da7f2 → Set) : Set where
  constructor s93d21f6e9b8c5177
  field
    s4da303d0733e594f : s3db164e6ee8da7f2
    s006e106e1a02f63b : sbdd4096159bc04ce s4da303d0733e594f
open s0ca58ef890d33dce

goal : {s3db164e6ee8da7f2 : Set} {sbdd4096159bc04ce sc4645a6d9c1a6f05 : s3db164e6ee8da7f2 → Set} → ((s66d9a8889b139949 : s3db164e6ee8da7f2) → sbdd4096159bc04ce s66d9a8889b139949 → sc4645a6d9c1a6f05 s66d9a8889b139949) → s0ca58ef890d33dce s3db164e6ee8da7f2 sbdd4096159bc04ce → s0ca58ef890d33dce s3db164e6ee8da7f2 sc4645a6d9c1a6f05
goal x (s93d21f6e9b8c5177 s4da303d0733e594f₁ s006e106e1a02f63b₁) = s93d21f6e9b8c5177
  s4da303d0733e594f₁
  ( x s4da303d0733e594f₁ s006e106e1a02f63b₁)
