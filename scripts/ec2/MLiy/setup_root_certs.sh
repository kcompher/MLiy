# The script must be sourced by install_MLiy.sh

# Copyright 2017 MLiy Contributors

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#      http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Change to Analyst home directory to install/configure 
cd ~analyst

# Add Custom roots certs to Linux truststore
cat ${CUSTOM_ROOT_CERTS} >> /etc/pki/tls/certs/ca-bundle.crt

# Add Custom root certs to JKS Store
keytool -import -noprompt -trustcacerts -alias -file  ${CUSTOM_ROOT_CERTS}  -keystore /etc/pki/java/cacerts -storepass changeit

rm -f *.crt

cd $SCRIPT_DIR