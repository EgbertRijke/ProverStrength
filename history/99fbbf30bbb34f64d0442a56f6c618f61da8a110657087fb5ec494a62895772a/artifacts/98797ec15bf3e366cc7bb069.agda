{-# OPTIONS --without-K --exact-split #-}
module Task where

goal : {s47ff242909bfcdf7 s3c7aced33f669eb9 s11057d5c557d28dd : Set} → (s47ff242909bfcdf7 → s3c7aced33f669eb9 → s11057d5c557d28dd) → s3c7aced33f669eb9 → s47ff242909bfcdf7 → s11057d5c557d28dd
goal = λ f y x → f x y
