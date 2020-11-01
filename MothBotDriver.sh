#!/bin/bash

export loop="loop"
while [ $loop == "loop" ]
do
  echo $(git pull)
  echo $(python3 MothBot.py)
done