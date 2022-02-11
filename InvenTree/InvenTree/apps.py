# -*- coding: utf-8 -*-

import logging

from django.apps import AppConfig
from django.core.exceptions import AppRegistryNotReady

from InvenTree.ready import isInTestMode, canAppAccessDatabase
import InvenTree.tasks


logger = logging.getLogger("inventree")


class InvenTreeConfig(AppConfig):
    name = 'InvenTree'

    def ready(self):

        if canAppAccessDatabase():

            self.remove_obsolete_tasks()

            self.start_background_tasks()

            if not isInTestMode():
                self.update_exchange_rates()

    def remove_obsolete_tasks(self):
        """
        Delete any obsolete scheduled tasks in the database
        """

        obsolete = [
            'InvenTree.tasks.delete_expired_sessions',
            'stock.tasks.delete_old_stock_items',
        ]

        try:
            from django_q.models import Schedule
        except (AppRegistryNotReady):
            return

        # Remove any existing obsolete tasks
        Schedule.objects.filter(func__in=obsolete).delete()

    def start_background_tasks(self):

        try:
            from django_q.models import Schedule
        except (AppRegistryNotReady):
            return

        logger.info("Starting background tasks...")

        # Remove successful task results from the database
        InvenTree.tasks.schedule_task(
            'InvenTree.tasks.delete_successful_tasks',
            schedule_type=Schedule.DAILY,
        )

        # Check for InvenTree updates
        InvenTree.tasks.schedule_task(
            'InvenTree.tasks.check_for_updates',
            schedule_type=Schedule.DAILY
        )

        # Heartbeat to let the server know the background worker is running
        InvenTree.tasks.schedule_task(
            'InvenTree.tasks.heartbeat',
            schedule_type=Schedule.MINUTES,
            minutes=15
        )

        # Keep exchange rates up to date
        InvenTree.tasks.schedule_task(
            'InvenTree.tasks.update_exchange_rates',
            schedule_type=Schedule.DAILY,
        )

        # Delete old error messages
        InvenTree.tasks.schedule_task(
            'InvenTree.tasks.delete_old_error_logs',
            schedule_type=Schedule.DAILY,
        )

        # Delete old notification records
        InvenTree.tasks.schedule_task(
            'common.tasks.delete_old_notifications',
            schedule_type=Schedule.DAILY,
        )

    def update_exchange_rates(self):
        """
        Update exchange rates each time the server is started, *if*:

        a) Have not been updated recently (one day or less)
        b) The base exchange rate has been altered
        """

        try:
            from djmoney.contrib.exchange.models import ExchangeBackend

            from InvenTree.tasks import update_exchange_rates
            from common.settings import currency_code_default
        except AppRegistryNotReady:
            pass

        base_currency = currency_code_default()

        update = False

        try:
            backend = ExchangeBackend.objects.get(name='InvenTreeExchange')

            last_update = backend.last_update

            if last_update is None:
                # Never been updated
                logger.info("Exchange backend has never been updated")
                update = True

            # Backend currency has changed?
            if not base_currency == backend.base_currency:
                logger.info(f"Base currency changed from {backend.base_currency} to {base_currency}")
                update = True

        except (ExchangeBackend.DoesNotExist):
            logger.info("Exchange backend not found - updating")
            update = True

        except:
            # Some other error - potentially the tables are not ready yet
            return

        if update:
            try:
                update_exchange_rates()
            except Exception as e:
                logger.error(f"Error updating exchange rates: {e}")
