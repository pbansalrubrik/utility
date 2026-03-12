#!/bin/bash

if [[ $1 == "" ]]; then
  echo "Useage: fill_sel.sh <threshold, discrete, both>"
  exit 1
fi

#sudo ipmitool sel clear
sleep 3

if [[ $1 == "threshold" ]] || \
   [[ $1 == "both" ]]; then
  sudo ipmitool sensor 2> /dev/null | grep -v discrete | sed 's/|.*//' |
  while read -r sensor_id; do
    echo "${sensor_id}-----------"
#    sudo ipmitool event "$sensor_id" unc asserted 2> /dev/null
#    sudo ipmitool event "$sensor_id" lnc asserted 2> /dev/null
    sudo ipmitool event "$sensor_id" ucr assert 2> /dev/null
    sudo ipmitool event "$sensor_id" unr assert 2> /dev/null
    sudo ipmitool event "$sensor_id" lnr assert 2> /dev/null
    sudo ipmitool event "$sensor_id" lcr assert 2> /dev/null
  done
fi

if [[ $1 == "discrete" ]] || \
   [[ $1 == "both" ]]; then
  STATES_BLOCK=0
  STATES=0
  SEL_COUNTER=0
  while read -r sensor_id; do
    echo "${sensor_id}-----------"
    while read -r state; do
      if [[ $STATES_BLOCK -eq 1 ]]; then
        STATES=1
      fi
      if [[ "$state" == "Sensor States:" ]]; then
        STATES_BLOCK=1
      fi
      if [[ "$state" == "Finding"* ]] ||
         [[ "$state" == "Sensor State Shortcuts:" ]]; then
        STATES_BLOCK=0
        STATES=0
      fi
      if [[ $STATES -eq 1 ]] &&
         [[ "$state" != "" ]]; then
# Uncomment the if below for HPE systems that only have 255 entries
# then make another run with -gt 255 to test all
#        if [[ $SEL_COUNTER -lt 255 ]]; then
          echo "sudo ipmitool event $sensor_id $state assert 2> /dev/null"
          sudo ipmitool event "$sensor_id" "$state" asserted 2> /dev/null
#        fi
        SEL_COUNTER=$((SEL_COUNTER + 1))
        echo "SEL_COUNTER= $SEL_COUNTER"
      fi
    done <<< "$(sudo ipmitool event "$sensor_id")"
  done <<< "$(sudo ipmitool sensor 2> /dev/null | grep discrete | sed 's/|.*//')"
fi

#ubuntu@R740xd:~/sel_sdr$ sudo ipmitool event "DIMM PG"
#Finding sensor DIMM PG... ok
#Sensor States:
#  State Deasserted
#  State Asserted
#Sensor State Shortcuts:
#  present    absent
#  assert     deassert
#  limit      nolimit
#  fail       nofail
#  yes        no
#  on         off
#  up         down
