"""
Odap web app main views
"""
'''
Copyright 2017 MLiy Contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

'''
from django.views import generic
from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from .settings import TIME_ZONE, MAX_INSTANCE_CACHE_AGE
from .models import Instance, Software_Config, GroupConfig, InstanceType, User
from . import forms
from .launch import launchInstanceThread
from .utils import has_permission
from datetime import datetime, timedelta
from pytz import timezone
import logging


### Code that does something
class Home(generic.TemplateView):
	template_name = 'odapweb/home.html'

	def get_context_data(self, **kwargs):
		context = super(generic.TemplateView, self).get_context_data(**kwargs)
		try:
			latest = Instance.objects.latest('updated_at')
			if latest is not None:
				updt_time = latest.updated_at
				context['cachetime'] = updt_time.astimezone(timezone(TIME_ZONE))  # .strftime('%Y-%m-%d %H:%M:%S %Z%z')
				if datetime.now(timezone('UTC')) > updt_time + timedelta(minutes=MAX_INSTANCE_CACHE_AGE):
					context['stale'] = True
			else:
				context['cachetime'] = "Never!"
		except Instance.DoesNotExist:
			context['cachetime'] = "Never!"

		return context


class UserDashboard(generic.TemplateView):
	template_name = 'odapweb/user-dashboard.html'


class PayDashboard(generic.TemplateView):
	template_name = 'odapweb/pay-dashboard.html'

	def get_context_data(self, **kwargs):
		context = super(generic.TemplateView, self).get_context_data(**kwargs)
		logger = logging.getLogger(__name__ + "." + self.__class__.__name__)
		username = str(self.request.user.username).upper()
		try:
			user = User.objects.get(username__iexact=username)
			user_group_set = set(user.groups.all())
			user_list = User.objects.all().order_by('username')
			context['user_list'] = []
			context['user_list'].append("All Users")
			# Make a list of all users that share the groups he's in
			for user in user_list:
				if user.username == 'admin':
					continue
				if set(user.groups.all()).isdisjoint(user_group_set):
					continue
				context['user_list'].append(user.username)
			group_list = user_group_set
			context['group_list'] = []
			context['group_list'].append("All Groups")
			# make a list of all groups he's in
			for grp in group_list:
				context['group_list'].append(grp.name)

		except Exception as e:
			context['group_list'] = []
			context['user_list'] = []
			logger.error(e)

		return context


class UserProfile(generic.TemplateView):
	template_name = 'odapweb/user-profile.html'


class InstanceView(generic.DetailView):
	"""
	Shows single instance record. The template page contains javascript to call the instance
	manipulation ajax.

	Because of the way permissions are implemented, the permissions hook needs to be in the
	get_object function.
	"""
	model = Instance
	template_name = 'odapweb/instanceview.html'

	def get_object(self, queryset=None):
		obj = super(generic.DetailView, self).get_object(queryset)
		if has_permission(self.request.user, obj.userid):
			return obj
		else:
			raise PermissionDenied


class SelectGrpConfig(generic.ListView):
	"""
	Step 1
	If a user is a member of more than one group, they will be
	prompted choose a group to proceed as.
	"""
	template_name = 'odapweb/pick-group-instance.html'

	def get_queryset(self, **kwargs):
		log = logging.getLogger(__name__)
		grpcfgs = GroupConfig.objects.filter(group__in=self.request.user.groups.all())
		log.debug("User %s has groupconfigs %s", self.request.user, grpcfgs)
		return grpcfgs


class SelectSwConfig(generic.ListView):
	"""
	Step 2 in user launching a new instance. This looks up
	the software configs the user is entitled to start.
	"""
	template_name = 'odapweb/pick-instance-type.html'

	def get_queryset(self, **kwargs):
		log = logging.getLogger(__name__)
		# ODAP-164 change query to:
		# software configs where grpid in permitted groups and
		# count(software_config.compatible_instancetypes - grpid.exclInstances ) > 0
		# as you can see the resulting django-ism approaches from the other side

		ugrp = GroupConfig.objects.get(pk=self.kwargs['grpid'])
		# old one
		# qs = Software_Config.objects.filter(permitted_groups=ugrp).distinct().order_by('name')
		qs = Software_Config.objects.filter(
			pk__in=InstanceType.objects.filter(software_config__permitted_groups=ugrp).exclude(
				pk__in=ugrp.exclInstances.all().values_list('pk', flat=True)).values_list('software_config__pk',
																						  flat=True).distinct()).order_by(
			'name')
		log.debug("software_config for user: %s", qs.values())

		return qs

	def get_context_data(self, **kwargs):
		context = super(generic.ListView, self).get_context_data(**kwargs)
		context['grpid'] = self.kwargs['grpid']
		return context


class SelectInstDetails(generic.FormView):
	"""
	Step 3 in specifying the instance to launch. The form class dynamically
	constructs widgets to present the options for launching the instance, based
	on what is set passed on in the initial data.

	In form_valid the instance is written to the database before being launched
	so that the right swconfig can be referenced. If the instance is wiped from the
	database at some point it'll be refreshed, but if there is more than one
	swconfig with the same ami id the manager won't be able to figure out
	which configuration that instance is running and will pick the first match.

	"""
	template_name = 'odapweb/pick-instance-details.html'
	form_class = forms.SelectInstDetailsForm

	def get_initial(self):
		initial = super(SelectInstDetails, self).get_initial()
		initial['user'] = self.request.user
		initial['swconfigid'] = self.kwargs['swconfigid']
		initial['grpid'] = self.kwargs['grpid']
		return initial

	def form_valid(self, form):
		# make logging specific so we can break it out
		logger = logging.getLogger(__name__ + "." + self.__class__.__name__)

		swconfig = get_object_or_404(Software_Config, pk=self.kwargs['swconfigid'])

		lit = launchInstanceThread(form, self.request.user, swconfig, self.kwargs)
		lit.start()
		logger.debug("Launch thread id is %s", lit.lid)
		self.success_url = reverse('launchingpage', kwargs={'launchid': lit.lid})

		return super(SelectInstDetails, self).form_valid(form)


class LaunchInterstitial(generic.TemplateView):
	"""
	container for the interstitial instance loading page
	"""
	template_name = 'odapweb/instance-launch-interstitial.html'

	def get_context_data(self, **kwargs):
		context = super(generic.TemplateView, self).get_context_data(**kwargs)
		context['launchid'] = kwargs['launchid']
		return context

# end of file
