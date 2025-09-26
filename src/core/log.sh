az monitor log-analytics workspace create --resource-group mypraxos --workspace-name mypraxos-pods

WORKSPACE_ID=$(az monitor log-analytics workspace show --resource-group mypraxos --workspace-name mypraxos-pods --query id -o tsv)

az aks enable-addons \
   -a monitoring \
   --name praxosCluster \
   --resource-group praxosKubernetes \
   --workspace-resource-id $WORKSPACE_ID




 az aks show \
   --resource-group praxosKubernetes \
   --name praxosCluster \
   --query "addonProfiles.omsagent.config.logAnalyticsWorkspaceResourceID" \
   -o ts