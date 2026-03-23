#!/bin/bash
cluster_id='cdm-cluster-v3mfjo-vpunbxa_ipv4'
if [ "$#" == 1 ]; then
    cluster_id="$1"
fi

echo $cluster_id


./deployment/cluster.sh $cluster_id exec nodes 'sdservice.sh envoy-controller stop'

./deployment/cluster.sh $cluster_id copy nodes ./src/cpp/build/current/envoy_ng/controller/envoy_controller_main /opt/rubrik/src/cpp/build/current/envoy_ng/controller/envoy_controller_main

./deployment/cluster.sh $cluster_id copy nodes ./src/cpp/build/current/envoy_ng/controller/envoycontroller_test_client_main /opt/rubrik/src/cpp/build/current/envoy_ng/controller/envoycontroller_test_client_main

./deployment/cluster.sh $cluster_id copy nodes ./bazel-out/k8-opt/bin/_solib_k8/*grpc* /opt/rubrik/src/_solib_k8/
./deployment/cluster.sh $cluster_id copy nodes ./bazel-out/k8-opt/bin/_solib_k8/libsrc_Scpp_Scode_Scompat_Siface_Slibiface.so /opt/rubrik/src/_solib_k8/
./deployment/cluster.sh $cluster_id copy nodes ./bazel-out/k8-opt/bin/_solib_k8/libsrc_Scpp_Scode_Splatform_Slibcpu.so /opt/rubrik/src/_solib_k8/

./deployment/cluster.sh $cluster_id copy nodes ./bazel-out/k8-out/bin/_solib_k8/*metrics* /opt/rubrik/src/_solib_k8/
#cdm/tools/builder.py --py --remote
#./deployment/cluster.sh $cluster_id deploy_conf

./deployment/cluster.sh $cluster_id exec nodes 'sdservice.sh envoy-controller start'
