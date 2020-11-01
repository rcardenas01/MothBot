#!/bin/bash

loop="loop"
export loop
while [ $loop == "loop" ]
do
  echo $(git pull)
  echo $(python3 MothBot.py)
done