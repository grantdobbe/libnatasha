#!/bin/bash


NODE=$1
SRC=$2

HOSTNAME=$(hostname)

if [ -z $1] 
  then
    echo "USE: configure-node nodename /path/containing/node-deploy"
    exit
fi

if [ -z $2] 
  then
    echo "USE: configure-node nodename /path/containing/node-deploy"
    exit
fi

echo "=====================\====================================="
echo "This installer will configure this machine to be an endrun"
echo "node. It will install any missing dependencies and change"
echo "system settings. Do not do this unless you are absolutely"
echo "sure of what you are doing."
echo "==========================================================="
echo "Do you want to continue? (y/n): "
read confirm
echo "==========================================================="

if ["$confirm" == "y"]; then
  echo "OK. Don't say we didn't warn you..."
  echo "Updating endrun install..."
  cd /home/$USER/endrun 
  git pull origin master
  echo "Done."
  
  cd /home/$USER/
  
  echo "Copying deployment files and setting up endrun repo..."
  rsync -a $SRC/$NODE-deploy $HOME/
  mv $HOME/$NODE-deploy $HOME/endrun-data
  echo "Done."
  
  echo "Creating endrun's config file..."
  cp $HOME/endrun/settings.conf.sample $HOME/endrun/settings.conf
  sed -i "s/nodeX/$NODE/g" $HOME/endrun/settings.conf
  echo "Done."
  
  echo "Adding ~/endrun to your path..."
  echo "export PATH=$PATH:$HOME/endrun" >> $HOME/.bashrc
  echo "Done."
  
  echo "Installing dependencies..."
  sudo apt-get -y install ruby ruby-dev libz-dev libicu-dev build-essential
  sudo gem install gollum
  echo "Done."
  
  echo "Changing host-specific settings..."
  sudo sed -i "s/$HOSTNAME/$NODE/g" /etc/hostname
  echo "+ Hostname modified"
  sudo sed -i "s/127\.0\.1\.1	$HOSTNAME/127\.0\.1\.1	$NODE/g" /etc/hosts
  echo "+ Hosts updated"
  sudo cp /home/$USER/endrun/install/gollum-server /etc/init.d/
  sudo sed -i "s;/home/pi/endrun-data/repo;$HOME/endrun-data/repo;g" /etc/init.d/gollum-server
  sudo chmod 755 /etc/init.d/gollum-server
  
  cp $HOME/endrun/install/config.rb $HOME/endrun-data/config.rb
  sed -i "s/nodeX/$NODE/g" $HOME/endrun-data/config.rb
  echo "+ Gollum configured"
  echo "Done."
  
  sudo update-rc.d gollum-server defaults
  #sudo cp $HOME/endrun/install/hostapd /etc/init.d/
  
  #echo "installing serial daemon"
  #sudo cp $HOME/endrun/endrun-daemon /etc/init.d/
  #sudo update-rc.d endrun-daemon default
  
  echo "Changing bundle paths..."
  sed -i "s;/home/(.*)/endrun-deploy/$NODE-deploy;$HOME/endrun-data;g" $HOME/endrun-data/repo/.git/config
  echo "Done."
  
  echo "Program complete. You may enter when ready."

else
  echo "Aborting."
fi
